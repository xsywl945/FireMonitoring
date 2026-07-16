package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import org.springframework.stereotype.Component;

@Component
public class IncidentStateMachine {
    public IncidentStatus target(IncidentStatus current, IncidentAction action) {
        return switch (action) {
            case ACKNOWLEDGE -> require(current == IncidentStatus.NEW, current, action, IncidentStatus.ACKNOWLEDGED);
            case START_HANDLING -> require(current == IncidentStatus.ACKNOWLEDGED, current, action, IncidentStatus.HANDLING);
            case RESOLVE -> require(current == IncidentStatus.HANDLING, current, action, IncidentStatus.RESOLVED);
            case MARK_FALSE_ALARM -> require(
                    current == IncidentStatus.NEW || current == IncidentStatus.ACKNOWLEDGED || current == IncidentStatus.HANDLING,
                    current, action, IncidentStatus.FALSE_ALARM);
        };
    }

    private static IncidentStatus require(boolean allowed, IncidentStatus current,
                                          IncidentAction action, IncidentStatus target) {
        if (!allowed) throw new ConflictException("Action " + action + " is not allowed while incident is " + current);
        return target;
    }
}
