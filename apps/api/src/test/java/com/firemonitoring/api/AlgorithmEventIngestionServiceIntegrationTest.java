package com.firemonitoring.api;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.events.*;
import com.firemonitoring.api.repository.*;
import com.firemonitoring.api.service.ResourceNotFoundException;
import com.firemonitoring.api.service.IncidentService;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import java.util.UUID;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@SpringBootTest
@ActiveProfiles("test")
class AlgorithmEventIngestionServiceIntegrationTest {
    @Autowired AlgorithmEventIngestionService ingestion;
    @Autowired ZoneRepository zones;
    @Autowired IncidentRepository incidents;
    @Autowired IncidentTimelineRepository timeline;
    @Autowired IncidentService incidentService;
    @MockitoSpyBean SimpMessagingTemplate messaging;

    @BeforeEach
    void resetMessagingSpy() { clearInvocations(messaging); }

    @Test
    void createsExactlyOneIncidentAndTimelineThenPublishes() {
        ZoneEntity zone = zones.save(new ZoneEntity("算法事件区域-" + UUID.randomUUID(), SceneType.LABORATORY));
        UUID eventId = UUID.randomUUID();
        String event = AlgorithmEventParserTest.confirmedEvent(eventId, zone.getId());
        long before = incidents.count();

        assertThat(ingestion.ingest(event)).isEqualTo(IngestionResult.CREATED);
        assertThat(ingestion.ingest(event)).isEqualTo(IngestionResult.DUPLICATE);
        assertThat(incidents.count()).isEqualTo(before + 1);

        IncidentEntity incident = incidents.findBySourceEventId(eventId.toString()).orElseThrow();
        assertThat(incident.getStatus()).isEqualTo(IncidentStatus.NEW);
        assertThat(incident.getTraceId()).isNotBlank();
        assertThat(incident.getDedupKey()).startsWith("zone-");
        assertThat(incident.getEventSource()).isEqualTo("inference-worker-1");
        assertThat(incident.getModelVersion()).isEqualTo("fire-yolo-dev");
        assertThat(incident.getFusionMode()).isEqualTo("DUAL_CAMERA");
        assertThat(incident.getObservationsJson()).contains("VIEW_A", "VIEW_B");
        assertThat(timeline.findByIncidentIdOrderByOccurredAtAsc(incident.getId()))
                .singleElement().extracting(IncidentTimelineEntity::getEventType)
                .isEqualTo("INCIDENT_CONFIRMED");
        verify(messaging, times(1)).convertAndSend(eq("/topic/incidents"), any(Object.class));
    }

    @Test
    void ignoresOtherEventTypesWithoutTouchingDatabase() {
        long before = incidents.count();
        String event = """
                {"eventId":"%s","eventType":"DETECTION_SUMMARY","schemaVersion":"1.0",
                 "occurredAt":"2026-07-16T08:00:00Z","traceId":"%s","source":"worker","payload":{}}
                """.formatted(UUID.randomUUID(), UUID.randomUUID());

        assertThat(ingestion.ingest(event)).isEqualTo(IngestionResult.IGNORED);
        assertThat(incidents.count()).isEqualTo(before);
        verifyNoInteractions(messaging);
    }

    @Test
    void missingZoneFailsWithoutRecordingEventSoItCanBeRetried() {
        UUID eventId = UUID.randomUUID();
        String event = AlgorithmEventParserTest.confirmedEvent(eventId, Long.MAX_VALUE);

        assertThatThrownBy(() -> ingestion.ingest(event)).isInstanceOf(ResourceNotFoundException.class);
        assertThat(incidents.existsBySourceEventId(eventId.toString())).isFalse();
        verifyNoInteractions(messaging);
    }

    @Test
    void attachesEvidenceAndSemanticAnalysisByTraceId() {
        ZoneEntity zone = zones.save(new ZoneEntity(
                "富化事件区域-" + UUID.randomUUID(), SceneType.CLASSROOM));
        UUID eventId = UUID.randomUUID();
        assertThat(ingestion.ingest(AlgorithmEventParserTest.confirmedEvent(eventId, zone.getId())))
                .isEqualTo(IngestionResult.CREATED);
        IncidentEntity incident = incidents.findBySourceEventId(eventId.toString()).orElseThrow();
        UUID traceId = UUID.fromString(incident.getTraceId());

        assertThat(ingestion.ingest(AlgorithmEventParserTest.evidenceEvent(traceId)))
                .isEqualTo(IngestionResult.CREATED);
        assertThat(ingestion.ingest(AlgorithmEventParserTest.vlmEvent(traceId)))
                .isEqualTo(IngestionResult.CREATED);

        IncidentEntity enriched = incidents.findById(incident.getId()).orElseThrow();
        assertThat(enriched.getObservationsJson()).contains("snapshotObjectKey", "detections");
        assertThat(enriched.getSemanticAnalysisJson()).contains("qwen3.7-plus", "Visible flame");
        var detail = incidentService.get(incident.getId());
        assertThat(detail.observations()).singleElement().satisfies(observation -> {
            assertThat(observation.snapshotAvailable()).isTrue();
            assertThat(observation.imageWidth()).isEqualTo(1280);
            assertThat(observation.detections()).hasSize(1);
        });
        assertThat(detail.semanticAnalysis().get("state").asText()).isEqualTo("COMPLETED");
        assertThat(detail.semanticAnalysis().get("summary").asText()).isEqualTo("Visible flame.");
        assertThat(timeline.findByIncidentIdOrderByOccurredAtAsc(incident.getId()))
                .extracting(IncidentTimelineEntity::getEventType)
                .containsExactly(
                        "INCIDENT_CONFIRMED",
                        "INCIDENT_EVIDENCE_READY",
                        "VLM_ANALYSIS_COMPLETED");
    }
}
