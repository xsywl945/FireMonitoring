package com.firemonitoring.api.events;

import java.util.List;

public record VlmAnalysisPayload(
        Long incidentId,
        String status,
        String provider,
        String model,
        String promptVersion,
        Boolean hasVisibleFire,
        Boolean hasVisibleSmoke,
        String sourceNature,
        String sceneType,
        String riskLevel,
        String reasoningSummary,
        List<String> recommendedActions,
        Double confidence,
        List<String> uncertainties,
        String errorCode,
        Double latencyMs) {}
