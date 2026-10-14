package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.ZoneEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ZoneRepository extends JpaRepository<ZoneEntity, Long> {
    boolean existsByNameAndIdNot(String name, Long id);
    boolean existsByName(String name);
}
