package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "incident_timeline")
public class IncidentTimelineEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false) @JoinColumn(name = "incident_id")
    private IncidentEntity incident;
    @Column(name = "event_type", nullable = false, length = 50)
    private String eventType;
    @Column(length = 2000)
    private String note;
    @Enumerated(EnumType.STRING) @Column(name = "false_alarm_reason", length = 40)
    private FalseAlarmReason falseAlarmReason;
    @Column(name = "actor_username", nullable = false, length = 50)
    private String actorUsername;
    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    protected IncidentTimelineEntity() {}
    public IncidentTimelineEntity(IncidentEntity incident, String eventType, String note,
                                  FalseAlarmReason falseAlarmReason, String actorUsername, Instant occurredAt) {
        this.incident = incident;
        this.eventType = eventType;
        this.note = note;
        this.falseAlarmReason = falseAlarmReason;
        this.actorUsername = actorUsername;
        this.occurredAt = occurredAt;
    }

    public Long getId() { return id; }
    public String getEventType() { return eventType; }
    public String getNote() { return note; }
    public FalseAlarmReason getFalseAlarmReason() { return falseAlarmReason; }
    public String getActorUsername() { return actorUsername; }
    public Instant getOccurredAt() { return occurredAt; }
}
