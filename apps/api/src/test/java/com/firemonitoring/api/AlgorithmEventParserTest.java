package com.firemonitoring.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.events.*;
import org.junit.jupiter.api.Test;
import org.springframework.http.converter.json.Jackson2ObjectMapperBuilder;

import java.util.UUID;

import static org.assertj.core.api.Assertions.*;

class AlgorithmEventParserTest {
    private final ObjectMapper objectMapper = Jackson2ObjectMapperBuilder.json().build();
    private final AlgorithmEventParser parser = new AlgorithmEventParser(objectMapper);

    @Test
    void parsesV1IncidentConfirmedEnvelopeAndPayload() {
        UUID eventId = UUID.randomUUID();
        ParsedIncidentConfirmedEvent parsed = parser.parseConfirmed(confirmedEvent(eventId, 7));

        assertThat(parsed.envelope().eventId()).isEqualTo(eventId);
        assertThat(parsed.envelope().zoneId()).isEqualTo(7);
        assertThat(parsed.payload().primaryType()).isEqualTo(PrimaryType.FIRE_AND_SMOKE);
        assertThat(parsed.payload().severity()).isEqualTo(Severity.HIGH);
        assertThat(parsed.payload().fusionMode()).isEqualTo(FusionMode.DUAL_CAMERA);
        assertThat(parsed.payload().observations()).hasSize(2);
        assertThat(parsed.observationsJson()).contains("VIEW_A", "smoke");
    }

    @Test
    void rejectsUnknownFieldsAndInvalidScores() {
        String unknown = confirmedEvent(UUID.randomUUID(), 1)
                .replace("\"source\":\"inference-worker-1\",", "\"source\":\"inference-worker-1\",\"unexpected\":true,");
        String invalidScore = confirmedEvent(UUID.randomUUID(), 1).replace("\"fusionScore\":0.91", "\"fusionScore\":1.2");

        assertThatThrownBy(() -> parser.parseConfirmed(unknown)).isInstanceOf(EventParseException.class);
        assertThatThrownBy(() -> parser.parseConfirmed(invalidScore)).isInstanceOf(EventParseException.class);
    }

    @Test
    void rejectsUnsupportedSchemaVersionAndMissingZone() {
        String wrongVersion = confirmedEvent(UUID.randomUUID(), 1).replace("\"schemaVersion\":\"1.0\"", "\"schemaVersion\":\"2.0\"");
        String missingZone = confirmedEvent(UUID.randomUUID(), 1).replace("\"zoneId\":1,", "");

        assertThatThrownBy(() -> parser.parseEnvelope(wrongVersion)).isInstanceOf(EventParseException.class);
        assertThatThrownBy(() -> parser.parseConfirmed(missingZone)).isInstanceOf(EventParseException.class);
    }

    @Test
    void parsesEvidenceAndVlmPayloads() {
        UUID traceId = UUID.randomUUID();
        ParsedIncidentEvidenceEvent evidence = parser.parseEvidence(evidenceEvent(traceId));
        ParsedVlmAnalysisEvent vlm = parser.parseVlm(vlmEvent(traceId));

        assertThat(evidence.payload().evidence()).singleElement().satisfies(frame -> {
            assertThat(frame.viewRole()).isEqualTo("SINGLE");
            assertThat(frame.snapshotObjectKey()).startsWith("incidents/");
            assertThat(frame.detections()).singleElement()
                    .extracting(EvidenceDetection::className).isEqualTo("fire");
        });
        assertThat(vlm.payload().status()).isEqualTo("SUCCEEDED");
        assertThat(vlm.payload().model()).isEqualTo("qwen3.7-plus");
        assertThat(vlm.payload().riskLevel()).isEqualTo("HIGH");
    }

    static String confirmedEvent(UUID eventId, long zoneId) {
        return confirmedEvent(eventId, UUID.randomUUID(), zoneId);
    }

    static String confirmedEvent(UUID eventId, UUID traceId, long zoneId) {
        return """
                {
                  "eventId":"%s",
                  "eventType":"INCIDENT_CONFIRMED",
                  "schemaVersion":"1.0",
                  "occurredAt":"2026-07-16T08:00:03Z",
                  "traceId":"%s",
                  "source":"inference-worker-1",
                  "siteId":1,
                  "zoneId":%d,
                  "cameraId":1,
                  "modelVersion":"fire-yolo-dev",
                  "payload":{
                    "dedupKey":"zone-%d-fire",
                    "primaryType":"FIRE_AND_SMOKE",
                    "severity":"HIGH",
                    "fusionMode":"DUAL_CAMERA",
                    "fusionScore":0.91,
                    "startedAt":"2026-07-16T08:00:00Z",
                    "confirmedAt":"2026-07-16T08:00:03Z",
                    "observations":[
                      {"cameraId":1,"viewRole":"VIEW_A","className":"fire","score":0.93,"effectiveFrames":4,"durationMs":800,"snapshotObjectKey":null},
                      {"cameraId":2,"viewRole":"VIEW_B","className":"smoke","score":0.86,"effectiveFrames":3,"durationMs":600,"snapshotObjectKey":null}
                    ]
                  }
                }
                """.formatted(eventId, traceId, zoneId, zoneId);
    }

    static String evidenceEvent(UUID traceId) {
        return """
                {
                  "eventId":"%s","eventType":"INCIDENT_EVIDENCE_READY","schemaVersion":"1.0",
                  "occurredAt":"2026-08-12T06:00:03Z","traceId":"%s","source":"inference-worker-1",
                  "siteId":1,"zoneId":1,"cameraId":1,"modelVersion":"fire-yolo-dev",
                  "payload":{"evidence":[{
                    "cameraId":1,"viewRole":"SINGLE","capturedAt":"2026-08-12T06:00:03Z",
                    "imageWidth":1280,"imageHeight":720,"temporalScore":0.84,
                    "snapshotObjectKey":"incidents/%s/frame.jpg",
                    "detections":[{"className":"fire","confidence":0.9,"bboxXyxy":[10,20,100,120]}]
                  }]}
                }
                """.formatted(UUID.randomUUID(), traceId, traceId);
    }

    static String vlmEvent(UUID traceId) {
        return """
                {
                  "eventId":"%s","eventType":"VLM_ANALYSIS_COMPLETED","schemaVersion":"1.0",
                  "occurredAt":"2026-08-12T06:00:04Z","traceId":"%s","source":"inference-worker-1",
                  "siteId":1,"zoneId":1,"cameraId":1,"modelVersion":"fire-yolo-dev",
                  "payload":{"status":"SUCCEEDED","provider":"dashscope","model":"qwen3.7-plus",
                    "promptVersion":"fire-risk-v2","hasVisibleFire":true,"hasVisibleSmoke":false,
                    "sourceNature":"open_flame","sceneType":"classroom","riskLevel":"HIGH",
                    "reasoningSummary":"Visible flame.","recommendedActions":["Verify the scene"],
                    "confidence":0.86,"uncertainties":[],"latencyMs":1200}
                }
                """.formatted(UUID.randomUUID(), traceId);
    }
}
