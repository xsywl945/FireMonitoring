package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.SceneType;
import com.firemonitoring.api.domain.ZoneStatus;

public record ZoneResponse(Long id, String name, SceneType sceneType, ZoneStatus status) {}
