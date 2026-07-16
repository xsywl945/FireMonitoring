package com.firemonitoring.api;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.service.*;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.*;

class IncidentStateMachineTest {
    private final IncidentStateMachine stateMachine = new IncidentStateMachine();

    @Test
    void allowsFalseAlarmFromAnyActiveStateButNotTerminalStates() {
        assertThat(stateMachine.target(IncidentStatus.NEW, IncidentAction.MARK_FALSE_ALARM))
                .isEqualTo(IncidentStatus.FALSE_ALARM);
        assertThat(stateMachine.target(IncidentStatus.HANDLING, IncidentAction.MARK_FALSE_ALARM))
                .isEqualTo(IncidentStatus.FALSE_ALARM);
        assertThatThrownBy(() -> stateMachine.target(IncidentStatus.RESOLVED, IncidentAction.MARK_FALSE_ALARM))
                .isInstanceOf(ConflictException.class);
    }
}
