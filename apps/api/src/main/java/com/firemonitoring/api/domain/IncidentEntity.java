package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "incidents")
public class IncidentEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false) @JoinColumn(name = "zone_id")
    private ZoneEntity zone;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 30)
    private IncidentStatus status;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20)
    private Severity severity;
    @Enumerated(EnumType.STRING) @Column(name = "primary_type", nullable = false, length = 30)
    private PrimaryType primaryType;
    @Column(name = "started_at", nullable = false)
    private Instant startedAt;
    @Column(name = "acknowledged_at")
    private Instant acknowledgedAt;
    @Column(name = "resolved_at")
    private Instant resolvedAt;
    @Column(name = "fusion_score", precision = 6, scale = 5)
    private BigDecimal fusionScore;
    @Column(name = "observations_json", columnDefinition = "TEXT")
    private String observationsJson;
    @Column(name = "semantic_analysis_json", columnDefinition = "TEXT")
    private String semanticAnalysisJson;
    @Version
    private long version;

    protected IncidentEntity() {}

    public IncidentEntity(ZoneEntity zone, Severity severity, PrimaryType primaryType, Instant startedAt, Double fusionScore) {
        this.zone = zone;
        this.status = IncidentStatus.NEW;
        this.severity = severity;
        this.primaryType = primaryType;
        this.startedAt = startedAt;
        this.fusionScore = fusionScore == null ? null : BigDecimal.valueOf(fusionScore);
        this.observationsJson = "[]";
    }

    public void transitionTo(IncidentStatus target, Instant at) {
        this.status = target;
        if (target == IncidentStatus.ACKNOWLEDGED && acknowledgedAt == null) acknowledgedAt = at;
        if (target == IncidentStatus.RESOLVED || target == IncidentStatus.FALSE_ALARM) resolvedAt = at;
    }

    public Long getId() { return id; }
    public ZoneEntity getZone() { return zone; }
    public IncidentStatus getStatus() { return status; }
    public Severity getSeverity() { return severity; }
    public PrimaryType getPrimaryType() { return primaryType; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getAcknowledgedAt() { return acknowledgedAt; }
    public Instant getResolvedAt() { return resolvedAt; }
    public Double getFusionScore() { return fusionScore == null ? null : fusionScore.doubleValue(); }
    public String getObservationsJson() { return observationsJson; }
    public String getSemanticAnalysisJson() { return semanticAnalysisJson; }
}
