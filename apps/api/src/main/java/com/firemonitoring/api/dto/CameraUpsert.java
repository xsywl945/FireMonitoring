package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.SourceType;
import jakarta.validation.constraints.*;

public record CameraUpsert(
        @NotBlank @Size(max = 100) String name,
        @NotNull SourceType sourceType,
        @Size(max = 1000) String sourceUri,
        @DecimalMin("1.0") @DecimalMax("30.0") Double targetFps) {}
