package com.firemonitoring.api.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.*;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.security.MessageDigest;
import java.util.*;

@Service
public class IncidentService {
    private final IncidentRepository incidents;
    private final IncidentTimelineRepository timeline;
    private final IdempotencyRecordRepository idempotency;
    private final IncidentStateMachine stateMachine;
    private final ObjectMapper objectMapper;
    private final SimpMessagingTemplate messaging;

    public IncidentService(IncidentRepository incidents, IncidentTimelineRepository timeline,
                           IdempotencyRecordRepository idempotency, IncidentStateMachine stateMachine,
                           ObjectMapper objectMapper, SimpMessagingTemplate messaging) {
        this.incidents = incidents;
        this.timeline = timeline;
        this.idempotency = idempotency;
        this.stateMachine = stateMachine;
        this.objectMapper = objectMapper;
        this.messaging = messaging;
    }

    @Transactional(readOnly = true)
    public List<IncidentSummary> list(IncidentStatus status, Severity severity) {
        List<IncidentEntity> result;
        if (status != null && severity != null) result = incidents.findByStatusAndSeverityOrderByStartedAtDesc(status, severity);
        else if (status != null) result = incidents.findByStatusOrderByStartedAtDesc(status);
        else if (severity != null) result = incidents.findBySeverityOrderByStartedAtDesc(severity);
        else result = incidents.findAllByOrderByStartedAtDesc();
        return result.stream().map(IncidentService::summary).toList();
    }

    @Transactional(readOnly = true)
    public IncidentDetail get(Long id) { return detail(find(id)); }

    @Transactional
    public IncidentDetail transition(Long id, UUID key, IncidentActionRequest request, String actor) {
        String fingerprint = fingerprint(request);
        var prior = idempotency.findByIdempotencyKey(key.toString());
        if (prior.isPresent()) {
            if (!prior.get().getIncidentId().equals(id) || prior.get().getRequestAction() != request.action()
                    || !prior.get().getRequestFingerprint().equals(fingerprint)) {
                throw new ConflictException("Idempotency-Key has already been used for another operation");
            }
            return readStoredResponse(prior.get().getResponseJson());
        }
        if (request.action() == IncidentAction.MARK_FALSE_ALARM && request.falseAlarmReason() == null) {
            throw new BadRequestException("falseAlarmReason is required when marking a false alarm");
        }
        IncidentEntity incident = find(id);
        IncidentStatus target = stateMachine.target(incident.getStatus(), request.action());
        Instant now = Instant.now();
        incident.transitionTo(target, now);
        incidents.save(incident);
        timeline.save(new IncidentTimelineEntity(incident, request.action().name(), blankToNull(request.note()),
                request.falseAlarmReason(), actor, now));
        IncidentDetail result = detail(incident);
        idempotency.save(new IdempotencyRecordEntity(key, id, request.action(), fingerprint, target, writeResponse(result)));
        messaging.convertAndSend("/topic/incidents", result);
        return result;
    }

    private IncidentEntity find(Long id) {
        return incidents.findById(id).orElseThrow(() -> new ResourceNotFoundException("Incident not found: " + id));
    }

    private IncidentDetail detail(IncidentEntity incident) {
        List<JsonNode> observations = readArray(incident.getObservationsJson());
        JsonNode semantic = readNode(incident.getSemanticAnalysisJson());
        List<Map<String, Object>> entries = timeline.findByIncidentIdOrderByOccurredAtAsc(incident.getId()).stream()
                .map(item -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("id", item.getId());
                    value.put("eventType", item.getEventType());
                    value.put("note", item.getNote());
                    value.put("falseAlarmReason", item.getFalseAlarmReason());
                    value.put("actorUsername", item.getActorUsername());
                    value.put("occurredAt", item.getOccurredAt());
                    return value;
                }).toList();
        return new IncidentDetail(incident.getId(), incident.getZone().getId(), incident.getZone().getName(),
                incident.getStatus(), incident.getSeverity(), incident.getPrimaryType(), incident.getStartedAt(),
                incident.getAcknowledgedAt(), incident.getFusionScore(), observations, semantic, entries);
    }

    private List<JsonNode> readArray(String json) {
        if (json == null || json.isBlank()) return List.of();
        try { return objectMapper.readValue(json, new TypeReference<>() {}); }
        catch (Exception e) { return List.of(); }
    }

    private JsonNode readNode(String json) {
        if (json == null || json.isBlank()) return null;
        try { return objectMapper.readTree(json); }
        catch (Exception e) { return null; }
    }

    private String fingerprint(IncidentActionRequest request) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(objectMapper.writeValueAsBytes(request));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (Exception exception) {
            throw new IllegalStateException("Unable to fingerprint idempotent request", exception);
        }
    }

    private String writeResponse(IncidentDetail response) {
        try { return objectMapper.writeValueAsString(response); }
        catch (Exception exception) { throw new IllegalStateException("Unable to store idempotent response", exception); }
    }

    private IncidentDetail readStoredResponse(String json) {
        try { return objectMapper.readValue(json, IncidentDetail.class); }
        catch (Exception exception) { throw new IllegalStateException("Unable to read idempotent response", exception); }
    }

    private static IncidentSummary summary(IncidentEntity incident) {
        return new IncidentSummary(incident.getId(), incident.getZone().getId(), incident.getZone().getName(),
                incident.getStatus(), incident.getSeverity(), incident.getPrimaryType(), incident.getStartedAt(),
                incident.getAcknowledgedAt());
    }

    private static String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }
}
