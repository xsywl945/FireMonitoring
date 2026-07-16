package com.firemonitoring.api.web;

import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class AuthController {
    private final AuthService auth;

    public AuthController(AuthService auth) { this.auth = auth; }

    @PostMapping("/auth/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) { return auth.login(request); }

    @GetMapping("/users/me")
    public UserResponse me(Authentication authentication) { return auth.currentUser(authentication.getName()); }
}
