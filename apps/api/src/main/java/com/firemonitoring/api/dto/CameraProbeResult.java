package com.firemonitoring.api.dto;

import java.time.Instant;

public record CameraProbeResult(boolean reachable, boolean configurationValid, Instant checkedAt, Integer width,
                                Integer height, Double fps, String message) {}
