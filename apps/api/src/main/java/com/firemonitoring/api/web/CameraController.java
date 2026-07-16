package com.firemonitoring.api.web;

import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.CameraService;
import jakarta.validation.Valid;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/cameras")
public class CameraController {
    private final CameraService cameras;

    public CameraController(CameraService cameras) { this.cameras = cameras; }

    @GetMapping
    public List<CameraResponse> list() { return cameras.list(); }

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public ResponseEntity<CameraResponse> create(@Valid @RequestBody CameraUpsert request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(cameras.create(request));
    }

    @PostMapping("/{cameraId}/probe")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public CameraProbeResult probe(@PathVariable Long cameraId) { return cameras.probe(cameraId); }

    @PostMapping("/{cameraId}/stream-ticket")
    public StreamTicket streamTicket(@PathVariable Long cameraId) { return cameras.createStreamTicket(cameraId); }
}
