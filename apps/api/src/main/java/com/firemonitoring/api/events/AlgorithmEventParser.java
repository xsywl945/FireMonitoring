package com.firemonitoring.api.events;

import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public class AlgorithmEventParser {
    private static final Set<String> VIEW_ROLES = Set.of("VIEW_A", "VIEW_B", "SINGLE");
    private static final Set<String> CLASSES = Set.of("fire", "smoke");
    private final ObjectMapper strictMapper;

    public AlgorithmEventParser(ObjectMapper objectMapper) {
        this.strictMapper = objectMapper.copy()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    }

    public AlgorithmEventEnvelope parseEnvelope(String json) {
        if (json == null || json.isBlank()) throw new EventParseException("Event JSON is empty");
        try {
            AlgorithmEventEnvelope envelope = strictMapper.readValue(json, AlgorithmEventEnvelope.class);
            validateEnvelope(envelope);
            return envelope;
        } catch (EventParseException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new EventParseException("Event envelope is not valid v1 JSON", exception);
        }
    }

    public ParsedIncidentConfirmedEvent parseConfirmed(String json) {
        AlgorithmEventEnvelope envelope = parseEnvelope(json);
        if (envelope.eventType() != AlgorithmEventType.INCIDENT_CONFIRMED) {
            throw new EventParseException("Expected INCIDENT_CONFIRMED event");
        }
        if (envelope.zoneId() == null || envelope.zoneId() < 1) {
            throw new EventParseException("zoneId is required for INCIDENT_CONFIRMED");
        }
        try {
            IncidentConfirmedPayload payload = strictMapper.treeToValue(envelope.payload(), IncidentConfirmedPayload.class);
            validatePayload(payload);
            String observations = strictMapper.writeValueAsString(payload.observations());
            return new ParsedIncidentConfirmedEvent(envelope, payload, observations);
        } catch (EventParseException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new EventParseException("INCIDENT_CONFIRMED payload is invalid", exception);
        }
    }

    private static void validateEnvelope(AlgorithmEventEnvelope event) {
        if (event.eventId() == null || event.eventType() == null || event.occurredAt() == null
                || event.traceId() == null || event.source() == null || event.source().isBlank()
                || event.source().length() > 100 || event.payload() == null || !event.payload().isObject()) {
            throw new EventParseException("Event envelope is missing required fields");
        }
        if (!"1.0".equals(event.schemaVersion())) throw new EventParseException("Unsupported schemaVersion");
        if (event.siteId() != null && event.siteId() < 1) throw new EventParseException("siteId must be positive");
        if (event.cameraId() != null && event.cameraId() < 1) throw new EventParseException("cameraId must be positive");
        if (event.modelVersion() != null && event.modelVersion().length() > 100) {
            throw new EventParseException("modelVersion is too long");
        }
    }

    private static void validatePayload(IncidentConfirmedPayload payload) {
        if (payload == null || payload.dedupKey() == null || payload.dedupKey().isBlank()
                || payload.dedupKey().length() > 200 || payload.primaryType() == null
                || payload.severity() == null || payload.fusionScore() == null
                || payload.fusionScore() < 0 || payload.fusionScore() > 1
                || payload.startedAt() == null || payload.confirmedAt() == null
                || payload.observations() == null || payload.observations().isEmpty()
                || payload.observations().size() > 2) {
            throw new EventParseException("INCIDENT_CONFIRMED payload is missing or violates required fields");
        }
        for (IncidentObservation observation : payload.observations()) {
            if (observation == null || observation.cameraId() == null || observation.cameraId() < 1
                    || !VIEW_ROLES.contains(observation.viewRole()) || !CLASSES.contains(observation.className())
                    || observation.score() == null || observation.score() < 0 || observation.score() > 1
                    || observation.effectiveFrames() == null || observation.effectiveFrames() < 1
                    || observation.durationMs() == null || observation.durationMs() < 0) {
                throw new EventParseException("Incident observation is invalid");
            }
        }
    }
}
