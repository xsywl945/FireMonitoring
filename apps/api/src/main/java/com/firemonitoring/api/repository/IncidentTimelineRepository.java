package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.IncidentTimelineEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface IncidentTimelineRepository extends JpaRepository<IncidentTimelineEntity, Long> {
    List<IncidentTimelineEntity> findByIncidentIdOrderByOccurredAtAsc(Long incidentId);
}
