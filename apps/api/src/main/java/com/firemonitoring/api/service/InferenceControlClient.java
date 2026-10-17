package com.firemonitoring.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.Map;

@Component
public class InferenceControlClient {
    private final ObjectMapper mapper;
    private final String baseUrl;
    private final String token;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

    public InferenceControlClient(ObjectMapper mapper,
                                  @Value("${app.inference.base-url}") String baseUrl,
                                  @Value("${app.inference.control-token}") String token) {
        this.mapper = mapper;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.token = token;
    }

    public JsonNode request(String path, Map<String, ?> body) {
        try {
            var builder = HttpRequest.newBuilder(URI.create(baseUrl + "/api/v1" + path))
                    .timeout(Duration.ofSeconds(12)).header("X-Control-Token", token);
            if (body == null) builder.GET();
            else builder.header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)));
            var response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
            JsonNode data = mapper.readTree(response.body());
            if (response.statusCode() == 409)
                throw new ConflictException(data.path("message").asText("设备正在运行"));
            if (response.statusCode() >= 400)
                throw new BadRequestException(data.path("message").asText("设备控制服务不可用"));
            return data;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BadRequestException("设备请求已中断");
        } catch (java.io.IOException exception) {
            throw new BadRequestException("设备控制服务未连接，请先启动推理服务");
        }
    }
}
