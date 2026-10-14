package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "zones")
public class ZoneEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, unique = true, length = 100)
    private String name;
    @Enumerated(EnumType.STRING) @Column(name = "scene_type", nullable = false, length = 30)
    private SceneType sceneType;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20)
    private ZoneStatus status;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected ZoneEntity() {}

    public ZoneEntity(String name, SceneType sceneType) {
        this.name = name;
        this.sceneType = sceneType;
        this.status = ZoneStatus.ENABLED;
        this.createdAt = Instant.now();
    }

    public void update(String name, SceneType sceneType) {
        this.name = name;
        this.sceneType = sceneType;
    }

    public void disable() { this.status = ZoneStatus.DISABLED; }

    public Long getId() { return id; }
    public String getName() { return name; }
    public SceneType getSceneType() { return sceneType; }
    public ZoneStatus getStatus() { return status; }
}
