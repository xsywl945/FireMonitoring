package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.CameraStatus;
import com.firemonitoring.api.domain.SourceType;
import com.firemonitoring.api.domain.ViewRole;
import java.time.Instant;

public record CameraResponse(Long id, String name, SourceType sourceType, String streamKey,
                             String maskedSource, CameraStatus status, Instant lastSeenAt,
                             Long zoneId, ViewRole viewRole, double targetFps) {}
