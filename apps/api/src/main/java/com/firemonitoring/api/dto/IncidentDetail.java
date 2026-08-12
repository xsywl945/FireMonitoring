package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.*;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public record IncidentDetail(Long id, Long zoneId, String zoneName, IncidentStatus status,
                             Severity severity, PrimaryType primaryType, Instant startedAt,
                             Instant acknowledgedAt, Double fusionScore,
                             List<IncidentObservationDetail> observations, com.fasterxml.jackson.databind.JsonNode semanticAnalysis,
                             List<Map<String, Object>> timeline) {}
