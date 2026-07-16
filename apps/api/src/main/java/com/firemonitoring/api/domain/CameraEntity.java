package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "cameras")
public class CameraEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 100)
    private String name;
    @Enumerated(EnumType.STRING) @Column(name = "source_type", nullable = false, length = 30)
    private SourceType sourceType;
    @Column(name = "source_uri", length = 1000)
    private String sourceUri;
    @Column(name = "stream_key", nullable = false, unique = true, length = 100)
    private String streamKey;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20)
    private CameraStatus status;
    @Column(name = "target_fps", nullable = false, precision = 5, scale = 2)
    private BigDecimal targetFps;
    @Column(name = "last_seen_at")
    private Instant lastSeenAt;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected CameraEntity() {}

    public CameraEntity(String name, SourceType sourceType, String sourceUri, Double targetFps) {
        this.name = name;
        this.sourceType = sourceType;
        this.sourceUri = sourceUri;
        this.targetFps = BigDecimal.valueOf(targetFps == null ? 5.0 : targetFps);
        this.streamKey = "camera-" + UUID.randomUUID();
        this.status = CameraStatus.UNKNOWN;
        this.createdAt = Instant.now();
    }

    public void recordProbe(boolean reachable, Instant checkedAt) {
        this.status = reachable ? CameraStatus.ONLINE : CameraStatus.OFFLINE;
        if (reachable) this.lastSeenAt = checkedAt;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public SourceType getSourceType() { return sourceType; }
    public String getSourceUri() { return sourceUri; }
    public String getStreamKey() { return streamKey; }
    public CameraStatus getStatus() { return status; }
    public double getTargetFps() { return targetFps.doubleValue(); }
    public Instant getLastSeenAt() { return lastSeenAt; }
}
