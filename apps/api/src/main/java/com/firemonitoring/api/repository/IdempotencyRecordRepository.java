package com.firemonitoring.api.repository;

import com.firemonitoring.api.domain.IdempotencyRecordEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface IdempotencyRecordRepository extends JpaRepository<IdempotencyRecordEntity, Long> {
    Optional<IdempotencyRecordEntity> findByIdempotencyKey(String key);
}
