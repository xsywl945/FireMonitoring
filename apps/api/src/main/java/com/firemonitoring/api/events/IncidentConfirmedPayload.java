package com.firemonitoring.api.events;

import com.firemonitoring.api.domain.PrimaryType;
import com.firemonitoring.api.domain.Severity;
import java.time.Instant;
import java.util.List;

public record IncidentConfirmedPayload(
        String dedupKey,
        PrimaryType primaryType,
        Severity severity,
        FusionMode fusionMode,
        Double fusionScore,
        Instant startedAt,
        Instant confirmedAt,
        List<IncidentObservation> observations) {}
