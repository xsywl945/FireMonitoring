package com.firemonitoring.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ApiIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;

    @Test
    void loginReturnsJwtAndCurrentUser() throws Exception {
        String token = login();
        mvc.perform(get("/api/v1/users/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("admin"))
                .andExpect(jsonPath("$.roles[0]").value("ADMIN"));
    }

    @Test
    void unauthenticatedRequestUsesConsistentErrorShape() throws Exception {
        mvc.perform(get("/api/v1/dashboard/summary"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().exists("X-Trace-Id"))
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.traceId", not(blankOrNullString())));
    }

    @Test
    void adminCanCreateAndBindTwoCamerasWithoutLeakingRtspPassword() throws Exception {
        String token = login();
        String suffix = UUID.randomUUID().toString().substring(0, 8);
        long zoneId = idFrom(mvc.perform(post("/api/v1/zones")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"实验室-%s","sceneType":"LABORATORY"}
                                """.formatted(suffix)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString());

        long cameraA = idFrom(mvc.perform(post("/api/v1/cameras")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"前置摄像头-%s","sourceType":"INTEGRATED","targetFps":5}
                                """.formatted(suffix)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString());
        long cameraB = idFrom(mvc.perform(post("/api/v1/cameras")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"网络摄像头-%s","sourceType":"NETWORK_RTSP",
                                 "sourceUri":"rtsp://operator:secret@192.0.2.10/live","targetFps":5}
                                """.formatted(suffix)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.maskedSource").value("rtsp://***:***@192.0.2.10/live"))
                .andExpect(content().string(not(containsString("secret"))))
                .andReturn().getResponse().getContentAsString());

        mvc.perform(put("/api/v1/zones/{zoneId}/camera-bindings", zoneId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                [{"cameraId":%d,"viewRole":"VIEW_A","weight":0.5},
                                 {"cameraId":%d,"viewRole":"VIEW_B","weight":0.5}]
                                """.formatted(cameraA, cameraB)))
                .andExpect(status().isNoContent());

        mvc.perform(post("/api/v1/cameras/{id}/probe", cameraB)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reachable").value(true));
        mvc.perform(post("/api/v1/cameras/{id}/stream-ticket", cameraA)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.whepUrl", endsWith("/whep")))
                .andExpect(jsonPath("$.hlsUrl", endsWith("/index.m3u8")));
    }

    @Test
    void validationErrorsExposeFieldNames() throws Exception {
        String token = login();
        mvc.perform(post("/api/v1/zones")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"sceneType\":\"CLASSROOM\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fieldErrors.name").exists());
    }

    private String login() throws Exception {
        String response = mvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"admin\",\"password\":\"FireAdmin123!\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken", not(blankOrNullString())))
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(response).get("accessToken").asText();
    }

    private long idFrom(String json) throws Exception {
        JsonNode node = objectMapper.readTree(json);
        return node.get("id").asLong();
    }
}
