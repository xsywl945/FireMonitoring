package com.firemonitoring.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.firemonitoring.api.domain.SourceType;
import com.firemonitoring.api.domain.ZoneStatus;
import com.firemonitoring.api.repository.CameraRepository;
import com.firemonitoring.api.repository.ZoneCameraBindingRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.Map;

@Service
public class LocalCameraService {
    private final CameraRepository cameras;
    private final ZoneCameraBindingRepository bindings;
    private final ObjectMapper mapper;
    private final String baseUrl;
    private final String token;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

    public LocalCameraService(CameraRepository cameras, ZoneCameraBindingRepository bindings,
                              ObjectMapper mapper,
                              @Value("${app.inference.base-url}") String baseUrl,
                              @Value("${app.inference.control-token}") String token) {
        this.cameras = cameras;
        this.bindings = bindings;
        this.mapper = mapper;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.token = token;
    }

    public JsonNode devices() { return request("", null); }

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
        return request("/start", Map.of("cameraId", id, "zoneId", binding.getZone().getId(),
                "cameraIndex", index, "targetFps", camera.getTargetFps()));
    }

    public JsonNode stop() { return request("/stop", Map.of()); }

    private JsonNode request(String path, Map<String, ?> body) {
        try {
            var builder = HttpRequest.newBuilder(URI.create(baseUrl + "/api/v1/local-cameras" + path))
                    .timeout(Duration.ofSeconds(12)).header("X-Control-Token", token);
            if (body == null) builder.GET();
            else builder.header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)));
            var response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            JsonNode data = mapper.readTree(response.body());
            if (response.statusCode() == 409)
                throw new ConflictException(data.path("message").asText("摄像头正在运行"));
            if (response.statusCode() >= 400)
                throw new BadRequestException(data.path("message").asText("摄像头服务不可用"));
            return data;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BadRequestException("摄像头请求已中断");
        } catch (java.io.IOException exception) {
            throw new BadRequestException("摄像头服务未连接，请先启动推理服务");
        }
    }
}
