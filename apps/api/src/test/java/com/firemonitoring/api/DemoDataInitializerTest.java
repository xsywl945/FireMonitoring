package com.firemonitoring.api;

import com.firemonitoring.api.config.DemoDataInitializer;
import com.firemonitoring.api.domain.UserEntity;
import com.firemonitoring.api.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class DemoDataInitializerTest {
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    @Test
    void migratesThePreviousDefaultPassword() {
        UserRepository users = mock(UserRepository.class);
        UserEntity user = new UserEntity("admin", "管理员", encoder.encode("FireAdmin123!"), List.of("ADMIN"));
        when(users.findByUsername("admin")).thenReturn(Optional.of(user));
        new DemoDataInitializer(users, encoder, "admin", "123456", "管理员").run(null);
        assertThat(encoder.matches("123456", user.getPasswordHash())).isTrue();
        verify(users).save(user);
    }

    @Test
    void preservesACustomPassword() {
        UserRepository users = mock(UserRepository.class);
        String hash = encoder.encode("custom-password");
        UserEntity user = new UserEntity("admin", "管理员", hash, List.of("ADMIN"));
        when(users.findByUsername("admin")).thenReturn(Optional.of(user));
        new DemoDataInitializer(users, encoder, "admin", "123456", "管理员").run(null);
        assertThat(user.getPasswordHash()).isEqualTo(hash);
        verify(users, never()).save(any());
    }
}
