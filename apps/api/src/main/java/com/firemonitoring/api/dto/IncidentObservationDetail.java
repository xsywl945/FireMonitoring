package com.firemonitoring.api.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;

public record IncidentObservationDetail(
        String id,
        Long cameraId,
        String viewRole,
        Instant capturedAt,
        String cameraName,
        Integer imageWidth,
        Integer imageHeight,
        List<JsonNode> detections,
        Double temporalScore,
        boolean snapshotAvailable) {}
