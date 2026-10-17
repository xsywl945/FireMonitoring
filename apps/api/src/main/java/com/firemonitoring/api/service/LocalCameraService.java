package com.firemonitoring.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.firemonitoring.api.domain.SourceType;
import com.firemonitoring.api.domain.ZoneStatus;
import com.firemonitoring.api.repository.CameraRepository;
import com.firemonitoring.api.repository.ZoneCameraBindingRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Service
public class LocalCameraService {
    private final CameraRepository cameras;
    private final ZoneCameraBindingRepository bindings;
    private final InferenceControlClient inference;

    public LocalCameraService(CameraRepository cameras, ZoneCameraBindingRepository bindings,
                              InferenceControlClient inference) {
        this.cameras = cameras;
        this.bindings = bindings;
        this.inference = inference;
    }

    public JsonNode devices() { return inference.request("/local-cameras", null); }

    @Transactional(readOnly = true)
    public JsonNode start(Long id) {
        var camera = cameras.findById(id).orElseThrow(() -> new ResourceNotFoundException("摄像头不存在"));
        if (camera.getSourceType() != SourceType.INTEGRATED && camera.getSourceType() != SourceType.USB)
            throw new BadRequestException("请选择本机或 USB 摄像头");
        var binding = bindings.findByCameraId(id)
                .orElseThrow(() -> new BadRequestException("请先绑定教室"));
        if (binding.getZone().getStatus() != ZoneStatus.ENABLED)
            throw new BadRequestException("教室已删除");
        String source = camera.getSourceUri();
        int index = camera.getSourceType() == SourceType.USB ? 1 : 0;
        if (source != null && !source.isBlank()) {
            if (!source.matches("\\d{1,2}")) throw new BadRequestException("请在摄像头设置中选择设备编号");
            index = Integer.parseInt(source);
        }
        return inference.request("/local-cameras/start", Map.of("cameraId", id, "zoneId", binding.getZone().getId(),
                "cameraIndex", index, "targetFps", camera.getTargetFps()));
    }

    public JsonNode stop() { return inference.request("/local-cameras/stop", Map.of()); }

    public JsonNode stop(Long id) {
        return inference.request("/local-cameras/stop", Map.of("cameraId", id));
    }
}
