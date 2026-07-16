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

    static String confirmedEvent(UUID eventId, long zoneId) {
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
                """.formatted(eventId, UUID.randomUUID(), zoneId, zoneId);
    }
}
