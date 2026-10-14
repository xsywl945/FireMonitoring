package com.firemonitoring.api.events;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.IncidentDetail;
import com.firemonitoring.api.repository.*;
import com.firemonitoring.api.service.*;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import org.springframework.transaction.support.*;

@Service
public class AlgorithmEventIngestionService {
    private final AlgorithmEventParser parser;
    private final IncidentRepository incidents;
    private final IncidentTimelineRepository timeline;
    private final ZoneRepository zones;
    private final IncidentService incidentService;
    private final SimpMessagingTemplate messaging;

    public AlgorithmEventIngestionService(AlgorithmEventParser parser, IncidentRepository incidents,
                                          IncidentTimelineRepository timeline, ZoneRepository zones,
                                          IncidentService incidentService, SimpMessagingTemplate messaging) {
        this.parser = parser;
        this.incidents = incidents;
        this.timeline = timeline;
        this.zones = zones;
        this.incidentService = incidentService;
        this.messaging = messaging;
    }

    @Transactional
    public IngestionResult ingest(String json) {
        AlgorithmEventEnvelope envelope = parser.parseEnvelope(json);
        return switch (envelope.eventType()) {
            case INCIDENT_CONFIRMED -> ingestConfirmed(json);
            case INCIDENT_EVIDENCE_READY -> ingestEvidence(json);
            case VLM_ANALYSIS_COMPLETED, VLM_ANALYSIS_FAILED -> ingestVlm(json);
            default -> IngestionResult.IGNORED;
        };
    }

    private IngestionResult ingestConfirmed(String json) {
        ParsedIncidentConfirmedEvent event = parser.parseConfirmed(json);
        String eventId = event.envelope().eventId().toString();
        if (incidents.existsBySourceEventId(eventId)) return IngestionResult.DUPLICATE;
        if (incidents.findFirstByTraceIdOrderByIdAsc(event.envelope().traceId().toString()).isPresent()) {
            return IngestionResult.DUPLICATE;
        }

        ZoneEntity zone = zones.findById(event.envelope().zoneId())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Algorithm event references missing zone: " + event.envelope().zoneId()));
        if (zone.getStatus() == ZoneStatus.DISABLED) return IngestionResult.IGNORED;
        IncidentConfirmedPayload payload = event.payload();
        IncidentEntity incident = IncidentEntity.fromAlgorithmEvent(zone, payload.severity(), payload.primaryType(),
                payload.startedAt(), payload.fusionScore(), event.observationsJson(), eventId,
                event.envelope().traceId().toString(), payload.dedupKey(), payload.confirmedAt(),
                event.envelope().source(), event.envelope().modelVersion(),
                payload.fusionMode() == null ? null : payload.fusionMode().name());
        incident = incidents.saveAndFlush(incident);
        String actor = event.envelope().source().length() <= 50
                ? event.envelope().source() : event.envelope().source().substring(0, 50);
        timeline.saveAndFlush(new IncidentTimelineEntity(incident, "INCIDENT_CONFIRMED",
                "eventId=" + eventId + ", traceId=" + event.envelope().traceId(), null,
                actor, payload.confirmedAt()));
        IncidentDetail detail = incidentService.get(incident.getId());
        publishAfterCommit(detail);
        return IngestionResult.CREATED;
    }

    private IngestionResult ingestEvidence(String json) {
        ParsedIncidentEvidenceEvent event = parser.parseEvidence(json);
        IncidentEntity incident = findByTrace(event.envelope());
        String note = eventNote(event.envelope());
        if (timeline.existsByIncidentIdAndEventTypeAndNote(
                incident.getId(), "INCIDENT_EVIDENCE_READY", note)) {
            return IngestionResult.DUPLICATE;
        }
        incident.replaceObservationsJson(event.evidenceJson());
        incidents.saveAndFlush(incident);
        timeline.saveAndFlush(new IncidentTimelineEntity(
                incident,
                "INCIDENT_EVIDENCE_READY",
                note,
                null,
                actor(event.envelope()),
                event.envelope().occurredAt()));
        publishAfterCommit(incidentService.get(incident.getId()));
        return IngestionResult.CREATED;
    }

    private IngestionResult ingestVlm(String json) {
        ParsedVlmAnalysisEvent event = parser.parseVlm(json);
        IncidentEntity incident = findByTrace(event.envelope());
        String eventType = event.envelope().eventType().name();
        String note = eventNote(event.envelope());
        if (timeline.existsByIncidentIdAndEventTypeAndNote(
                incident.getId(), eventType, note)) {
            return IngestionResult.DUPLICATE;
        }
        incident.replaceSemanticAnalysisJson(event.analysisJson());
        incidents.saveAndFlush(incident);
        timeline.saveAndFlush(new IncidentTimelineEntity(
                incident,
                eventType,
                note,
                null,
                actor(event.envelope()),
                event.envelope().occurredAt()));
        publishAfterCommit(incidentService.get(incident.getId()));
        return IngestionResult.CREATED;
    }

    private IncidentEntity findByTrace(AlgorithmEventEnvelope envelope) {
        return incidents.findFirstByTraceIdOrderByIdAsc(envelope.traceId().toString())
                .orElseThrow(() -> new ResourceNotFoundException(
                        "Algorithm event references missing trace: " + envelope.traceId()));
    }

    private static String eventNote(AlgorithmEventEnvelope envelope) {
        return "eventId=" + envelope.eventId();
    }

    private static String actor(AlgorithmEventEnvelope envelope) {
        return envelope.source().length() <= 50
                ? envelope.source() : envelope.source().substring(0, 50);
    }

    private void publishAfterCommit(IncidentDetail detail) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            messaging.convertAndSend("/topic/incidents", detail);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() { messaging.convertAndSend("/topic/incidents", detail); }
        });
    }
}
