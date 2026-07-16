package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.DashboardSummary;
import com.firemonitoring.api.repository.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;

@Service
public class DashboardService {
    private final CameraRepository cameras;
    private final IncidentRepository incidents;

    public DashboardService(CameraRepository cameras, IncidentRepository incidents) {
        this.cameras = cameras;
        this.incidents = incidents;
    }

    @Transactional(readOnly = true)
    public DashboardSummary summary() {
        Instant startOfToday = LocalDate.now(ZoneId.of("Asia/Shanghai"))
                .atStartOfDay(ZoneId.of("Asia/Shanghai")).toInstant();
        return new DashboardSummary(cameras.countByStatus(CameraStatus.ONLINE), cameras.count(),
                incidents.countByStatus(IncidentStatus.NEW), incidents.countByStatus(IncidentStatus.HANDLING),
                incidents.countByStartedAtGreaterThanEqual(startOfToday));
    }
}
