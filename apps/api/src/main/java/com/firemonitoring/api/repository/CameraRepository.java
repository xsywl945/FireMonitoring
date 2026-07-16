package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.CameraEntity;
import com.firemonitoring.api.domain.CameraStatus;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CameraRepository extends JpaRepository<CameraEntity, Long> {
    long countByStatus(CameraStatus status);
}
