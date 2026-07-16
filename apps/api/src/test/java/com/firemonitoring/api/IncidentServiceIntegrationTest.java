package com.firemonitoring.api;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.IncidentActionRequest;
import com.firemonitoring.api.repository.*;
import com.firemonitoring.api.service.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class IncidentServiceIntegrationTest {
    @Autowired IncidentService service;
    @Autowired IncidentRepository incidents;
    @Autowired ZoneRepository zones;

    private IncidentEntity incident;

    @BeforeEach
    void createIncident() {
        ZoneEntity zone = zones.save(new ZoneEntity("状态机测试-" + UUID.randomUUID(), SceneType.CLASSROOM));
        incident = incidents.save(new IncidentEntity(zone, Severity.HIGH, PrimaryType.FIRE,
                Instant.now(), 0.91));
    }

    @Test
    void followsStateMachineAndReplaysSameIdempotencyKey() {
        UUID key = UUID.randomUUID();
        var acknowledged = service.transition(incident.getId(), key,
                new IncidentActionRequest(IncidentAction.ACKNOWLEDGE, "已确认", null), "admin");
        var replay = service.transition(incident.getId(), key,
                new IncidentActionRequest(IncidentAction.ACKNOWLEDGE, "已确认", null), "admin");

        assertThat(acknowledged.status()).isEqualTo(IncidentStatus.ACKNOWLEDGED);
        assertThat(replay.status()).isEqualTo(IncidentStatus.ACKNOWLEDGED);
        assertThat(replay.timeline()).hasSize(1);

        var handling = service.transition(incident.getId(), UUID.randomUUID(),
                new IncidentActionRequest(IncidentAction.START_HANDLING, null, null), "admin");
        var resolved = service.transition(incident.getId(), UUID.randomUUID(),
                new IncidentActionRequest(IncidentAction.RESOLVE, "处理结束", null), "admin");
        assertThat(handling.status()).isEqualTo(IncidentStatus.HANDLING);
        assertThat(resolved.status()).isEqualTo(IncidentStatus.RESOLVED);
        assertThat(resolved.timeline()).hasSize(3);
    }

    @Test
    void rejectsIllegalTransitionAndIdempotencyKeyReuse() {
        UUID key = UUID.randomUUID();
        service.transition(incident.getId(), key,
                new IncidentActionRequest(IncidentAction.ACKNOWLEDGE, null, null), "admin");

        assertThatThrownBy(() -> service.transition(incident.getId(), UUID.randomUUID(),
                new IncidentActionRequest(IncidentAction.RESOLVE, null, null), "admin"))
                .isInstanceOf(ConflictException.class);
        assertThatThrownBy(() -> service.transition(incident.getId(), key,
                new IncidentActionRequest(IncidentAction.START_HANDLING, null, null), "admin"))
                .isInstanceOf(ConflictException.class);
    }

    @Test
    void falseAlarmRequiresReason() {
        assertThatThrownBy(() -> service.transition(incident.getId(), UUID.randomUUID(),
                new IncidentActionRequest(IncidentAction.MARK_FALSE_ALARM, null, null), "admin"))
                .isInstanceOf(BadRequestException.class);
    }
}
