package com.firemonitoring.api.events;

public record ParsedVlmAnalysisEvent(
        AlgorithmEventEnvelope envelope,
        VlmAnalysisPayload payload,
        String analysisJson) {}
