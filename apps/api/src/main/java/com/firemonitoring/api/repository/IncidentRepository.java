package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.*;
import org.springframework.data.jpa.repository.JpaRepository;
import java.time.Instant;
import java.util.List;

public interface IncidentRepository extends JpaRepository<IncidentEntity, Long> {
    List<IncidentEntity> findAllByOrderByStartedAtDesc();
    List<IncidentEntity> findByStatusOrderByStartedAtDesc(IncidentStatus status);
    List<IncidentEntity> findBySeverityOrderByStartedAtDesc(Severity severity);
    List<IncidentEntity> findByStatusAndSeverityOrderByStartedAtDesc(IncidentStatus status, Severity severity);
    long countByStatus(IncidentStatus status);
    long countByStartedAtGreaterThanEqual(Instant from);
}
