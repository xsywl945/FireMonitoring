package com.firemonitoring.api.dto;

import com.fasterxml.jackson.databind.JsonNode;

public record IncidentAnalysis(IncidentSummary incident, JsonNode semanticAnalysis) {}
