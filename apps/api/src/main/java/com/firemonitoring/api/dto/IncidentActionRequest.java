package com.firemonitoring.api.dto;

import com.firemonitoring.api.domain.FalseAlarmReason;
import com.firemonitoring.api.domain.IncidentAction;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record IncidentActionRequest(
        @NotNull IncidentAction action,
        @Size(max = 2000) String note,
        FalseAlarmReason falseAlarmReason) {}
