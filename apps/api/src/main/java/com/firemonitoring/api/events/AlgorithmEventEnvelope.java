package com.firemonitoring.api.events;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.UUID;

public record AlgorithmEventEnvelope(
        UUID eventId,
        AlgorithmEventType eventType,
        String schemaVersion,
        Instant occurredAt,
        UUID traceId,
        String source,
        Long siteId,
        Long zoneId,
        Long cameraId,
        String modelVersion,
        JsonNode payload) {}
