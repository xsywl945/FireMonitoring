package com.firemonitoring.api.events;

public record ParsedIncidentConfirmedEvent(
        AlgorithmEventEnvelope envelope,
        IncidentConfirmedPayload payload,
        String observationsJson) {}
