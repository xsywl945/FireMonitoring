package com.firemonitoring.api.events;

import java.time.Instant;
import java.util.List;

public record EvidenceFramePayload(
        Long cameraId,
        String viewRole,
        Instant capturedAt,
        Integer imageWidth,
        Integer imageHeight,
        List<EvidenceDetection> detections,
        Double temporalScore,
        String snapshotObjectKey) {}
