package com.firemonitoring.api.events;

public record ParsedIncidentEvidenceEvent(
        AlgorithmEventEnvelope envelope,
        IncidentEvidenceReadyPayload payload,
        String evidenceJson) {}
