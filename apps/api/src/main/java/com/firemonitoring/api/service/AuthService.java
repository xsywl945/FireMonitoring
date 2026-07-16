package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.UserEntity;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.UserRepository;
import com.firemonitoring.api.security.JwtService;
import org.springframework.security.authentication.*;
import org.springframework.stereotype.Service;

@Service
public class AuthService {
    private final AuthenticationManager authenticationManager;
    private final UserRepository users;
    private final JwtService jwtService;

    public AuthService(AuthenticationManager authenticationManager, UserRepository users, JwtService jwtService) {
        this.authenticationManager = authenticationManager;
        this.users = users;
        this.jwtService = jwtService;
    }

    public AuthResponse login(LoginRequest request) {
        authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(request.username(), request.password()));
        UserEntity user = getUser(request.username());
        return new AuthResponse(jwtService.issue(user), jwtService.expirationSeconds(), toResponse(user));
    }

    public UserResponse currentUser(String username) { return toResponse(getUser(username)); }

    private UserEntity getUser(String username) {
        return users.findByUsername(username).orElseThrow(() -> new ResourceNotFoundException("User not found"));
    }

    private static UserResponse toResponse(UserEntity user) {
        return new UserResponse(user.getId(), user.getUsername(), user.getDisplayName(), user.getRoleList());
    }
}
