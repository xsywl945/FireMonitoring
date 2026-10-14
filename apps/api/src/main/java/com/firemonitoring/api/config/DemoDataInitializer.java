package com.firemonitoring.api.config;

import com.firemonitoring.api.domain.UserEntity;
import com.firemonitoring.api.repository.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class DemoDataInitializer implements ApplicationRunner {
    private final UserRepository users;
    private final PasswordEncoder passwordEncoder;
    private final String username;
    private final String password;
    private final String displayName;

    public DemoDataInitializer(UserRepository users, PasswordEncoder passwordEncoder,
                               @Value("${app.demo.admin-username}") String username,
                               @Value("${app.demo.admin-password}") String password,
                               @Value("${app.demo.admin-display-name}") String displayName) {
        this.users = users;
        this.passwordEncoder = passwordEncoder;
        this.username = username;
        this.password = password;
        this.displayName = displayName;
    }

    @Override
    public void run(ApplicationArguments args) {
        var existing = users.findByUsername(username);
        if (existing.isEmpty()) {
            users.save(new UserEntity(username, displayName, passwordEncoder.encode(password), List.of("ADMIN")));
        } else if ("123456".equals(password)
                && passwordEncoder.matches("FireAdmin123!", existing.get().getPasswordHash())) {
            existing.get().changePassword(passwordEncoder.encode(password));
            users.save(existing.get());
        }
    }
}
