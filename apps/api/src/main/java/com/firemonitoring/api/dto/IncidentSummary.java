package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.*;
import java.time.Instant;

public record IncidentSummary(Long id, Long zoneId, String zoneName, IncidentStatus status,
                              Severity severity, PrimaryType primaryType, Instant startedAt,
                              Instant acknowledgedAt) {}
