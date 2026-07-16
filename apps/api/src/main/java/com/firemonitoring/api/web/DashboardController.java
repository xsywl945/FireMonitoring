package com.firemonitoring.api.web;

import com.firemonitoring.api.dto.DashboardSummary;
import com.firemonitoring.api.service.DashboardService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/dashboard")
public class DashboardController {
    private final DashboardService dashboard;

    public DashboardController(DashboardService dashboard) { this.dashboard = dashboard; }

    @GetMapping("/summary")
    public DashboardSummary summary() { return dashboard.summary(); }
}
