package com.firemonitoring.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.firemonitoring.api.service.InferenceControlClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class PumpControllerIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockitoBean InferenceControlClient inference;

    @Test
    void anonymousCannotReadPumpStatus() throws Exception {
        mvc.perform(get("/api/v1/pump")).andExpect(status().isUnauthorized());
        verifyNoInteractions(inference);
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCanReadButCannotStopPump() throws Exception {
        when(inference.request("/pump", null)).thenReturn(mapper.readTree("{\"enabled\":false}"));
        mvc.perform(get("/api/v1/pump")).andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").value(false));
        mvc.perform(post("/api/v1/pump/stop")).andExpect(status().isForbidden());
        verify(inference, never()).request(eq("/pump/stop"), any());
    }

    @Test
    @WithMockUser(roles = "OPERATOR")
    void operatorCanStopAndLatchAutomaticSuppression() throws Exception {
        when(inference.request("/pump/stop", Map.of()))
                .thenReturn(mapper.readTree("{\"inhibited\":true,\"deviceState\":\"OFF\"}"));
        mvc.perform(post("/api/v1/pump/stop")).andExpect(status().isOk())
                .andExpect(jsonPath("$.inhibited").value(true))
                .andExpect(jsonPath("$.deviceState").value("OFF"));
    }
}
