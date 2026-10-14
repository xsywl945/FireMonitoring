package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.*;
import org.springframework.data.jpa.repository.JpaRepository;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface IncidentRepository extends JpaRepository<IncidentEntity, Long> {
    List<IncidentEntity> findAllByOrderByStartedAtDesc();
    List<IncidentEntity> findByStatusOrderByStartedAtDesc(IncidentStatus status);
    List<IncidentEntity> findBySeverityOrderByStartedAtDesc(Severity severity);
    List<IncidentEntity> findByStatusAndSeverityOrderByStartedAtDesc(IncidentStatus status, Severity severity);
    long countByStatus(IncidentStatus status);
    long countByStartedAtGreaterThanEqual(Instant from);
    boolean existsByZoneId(Long zoneId);
    boolean existsBySourceEventId(String sourceEventId);
    Optional<IncidentEntity> findBySourceEventId(String sourceEventId);
    Optional<IncidentEntity> findFirstByTraceIdOrderByIdAsc(String traceId);
}
