package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.ZoneCameraBindingEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ZoneCameraBindingRepository extends JpaRepository<ZoneCameraBindingEntity, Long> {
    void deleteAllByCameraId(Long cameraId);
    void deleteAllByZoneId(Long zoneId);
    Optional<ZoneCameraBindingEntity> findByCameraId(Long cameraId);
}
