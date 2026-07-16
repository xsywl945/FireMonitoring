package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.SceneType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ZoneUpsert(
        @NotBlank @Size(max = 100) String name,
        @NotNull SceneType sceneType) {}
