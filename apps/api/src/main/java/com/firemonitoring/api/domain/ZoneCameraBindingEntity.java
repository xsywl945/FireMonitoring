package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "zone_camera_bindings")
public class ZoneCameraBindingEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false) @JoinColumn(name = "zone_id")
    private ZoneEntity zone;
    @ManyToOne(fetch = FetchType.LAZY, optional = false) @JoinColumn(name = "camera_id")
    private CameraEntity camera;
    @Enumerated(EnumType.STRING) @Column(name = "view_role", nullable = false, length = 20)
    private ViewRole viewRole;
    @Column(nullable = false, precision = 5, scale = 4)
    private BigDecimal weight;

    protected ZoneCameraBindingEntity() {}
    public ZoneCameraBindingEntity(ZoneEntity zone, CameraEntity camera, ViewRole viewRole, double weight) {
        this.zone = zone;
        this.camera = camera;
        this.viewRole = viewRole;
        this.weight = BigDecimal.valueOf(weight);
    }
}
