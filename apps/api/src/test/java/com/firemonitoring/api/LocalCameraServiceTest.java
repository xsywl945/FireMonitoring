package com.firemonitoring.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.repository.*;
import com.firemonitoring.api.service.LocalCameraService;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class LocalCameraServiceTest {
    @Test
    void startUsesSavedDeviceIndexAndRoomAndKeepsControlTokenServerSide() throws Exception {
        var mapper = new ObjectMapper();
        var cameras = mock(CameraRepository.class);
        var bindings = mock(ZoneCameraBindingRepository.class);
        var camera = new CameraEntity("USB", SourceType.USB, "2", 4.0);
        ReflectionTestUtils.setField(camera, "id", 9L);
        var room = new ZoneEntity("301", SceneType.CLASSROOM);
        ReflectionTestUtils.setField(room, "id", 7L);
        when(cameras.findById(9L)).thenReturn(Optional.of(camera));
        when(bindings.findByCameraId(9L)).thenReturn(Optional.of(
                new ZoneCameraBindingEntity(room, camera, ViewRole.SINGLE, 1.0)));
        var received = new AtomicReference<String>();
        var receivedToken = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/v1/local-cameras/start", exchange -> {
            received.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            receivedToken.set(exchange.getRequestHeaders().getFirst("X-Control-Token"));
            byte[] response = "{\"status\":\"STARTING\"}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(202, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        try {
            var service = new LocalCameraService(cameras, bindings, mapper,
                    "http://127.0.0.1:" + server.getAddress().getPort(), "test-control-token");
            assertThat(service.start(9L).path("status").asText()).isEqualTo("STARTING");
            var payload = mapper.readTree(received.get());
            assertThat(payload.path("cameraIndex").asInt()).isEqualTo(2);
            assertThat(payload.path("zoneId").asInt()).isEqualTo(7);
            assertThat(payload.path("targetFps").asDouble()).isEqualTo(4.0);
            assertThat(receivedToken.get()).isEqualTo("test-control-token");
            assertThat(received.get()).doesNotContain("test-control-token");
        } finally {
            server.stop(0);
        }
    }
}
