package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.ViewRole;
import jakarta.validation.constraints.*;

public record CameraBindingRequest(
        @NotNull @Positive Long cameraId,
        @NotNull ViewRole viewRole,
        @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double weight) {}
