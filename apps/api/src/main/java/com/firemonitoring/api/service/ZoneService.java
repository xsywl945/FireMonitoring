package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

@Service
public class ZoneService {
    private final ZoneRepository zones;
    private final CameraRepository cameras;
    private final ZoneCameraBindingRepository bindings;

    public ZoneService(ZoneRepository zones, CameraRepository cameras, ZoneCameraBindingRepository bindings) {
        this.zones = zones;
        this.cameras = cameras;
        this.bindings = bindings;
    }

    @Transactional(readOnly = true)
    public List<ZoneResponse> list() { return zones.findAll().stream().map(ZoneService::map).toList(); }

    @Transactional
    public ZoneResponse create(ZoneUpsert request) {
        String name = request.name().trim();
        if (zones.existsByName(name)) throw new ConflictException("Zone name already exists");
        return map(zones.save(new ZoneEntity(name, request.sceneType())));
    }

    @Transactional
    public void replaceBindings(Long zoneId, List<CameraBindingRequest> requests) {
        ZoneEntity zone = zones.findById(zoneId)
                .orElseThrow(() -> new ResourceNotFoundException("Zone not found: " + zoneId));
        Set<Long> cameraIds = new HashSet<>();
        Set<ViewRole> roles = new HashSet<>();
        for (CameraBindingRequest request : requests) {
            if (!cameraIds.add(request.cameraId())) throw new BadRequestException("A camera may only be bound once per zone");
            if (!roles.add(request.viewRole())) throw new BadRequestException("Each view role may only be used once per zone");
        }
        Map<Long, CameraEntity> byId = new HashMap<>();
        cameras.findAllById(cameraIds).forEach(camera -> byId.put(camera.getId(), camera));
        if (byId.size() != cameraIds.size()) throw new ResourceNotFoundException("One or more cameras do not exist");
        bindings.deleteAllByZoneId(zoneId);
        bindings.flush();
        bindings.saveAll(requests.stream().map(request -> new ZoneCameraBindingEntity(
                zone, byId.get(request.cameraId()), request.viewRole(), request.weight())).toList());
    }

    private static ZoneResponse map(ZoneEntity zone) {
        return new ZoneResponse(zone.getId(), zone.getName(), zone.getSceneType(), zone.getStatus());
    }
}
