package com.firemonitoring.api.web;

import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.CameraService;
import com.firemonitoring.api.service.LocalCameraService;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/cameras")
public class CameraController {
    private final CameraService cameras;

    private final LocalCameraService local;

    public CameraController(CameraService cameras, LocalCameraService local) {
        this.cameras = cameras;
        this.local = local;
    }

    @GetMapping("/local-devices")
    public JsonNode localDevices() { return local.devices(); }

    @PostMapping("/{cameraId}/start")
    @ResponseStatus(HttpStatus.ACCEPTED)
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public JsonNode start(@PathVariable Long cameraId) { return local.start(cameraId); }

    @PostMapping("/local-stop")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public JsonNode stop() { return local.stop(); }

    @GetMapping
    public List<CameraResponse> list() { return cameras.list(); }

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public ResponseEntity<CameraResponse> create(@Valid @RequestBody CameraUpsert request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(cameras.create(request));
    }

    @PutMapping("/{cameraId}")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public CameraResponse update(@PathVariable Long cameraId, @Valid @RequestBody CameraUpsert request) {
        return cameras.update(cameraId, request);
    }

    @DeleteMapping("/{cameraId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public void delete(@PathVariable Long cameraId) { cameras.delete(cameraId); }

    @PostMapping("/{cameraId}/probe")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public CameraProbeResult probe(@PathVariable Long cameraId) { return cameras.probe(cameraId); }

    @PostMapping("/{cameraId}/stream-ticket")
    public StreamTicket streamTicket(@PathVariable Long cameraId) { return cameras.createStreamTicket(cameraId); }
}
