package com.firemonitoring.api.events;

public record IncidentObservation(
        Long cameraId,
        String viewRole,
        String className,
        Double score,
        Integer effectiveFrames,
        Long durationMs,
        String snapshotObjectKey) {}
