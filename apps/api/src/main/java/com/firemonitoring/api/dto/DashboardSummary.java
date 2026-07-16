package com.firemonitoring.api.dto;

public record DashboardSummary(long onlineCameras, long totalCameras, long newIncidents,
                               long handlingIncidents, long todayIncidents) {}
