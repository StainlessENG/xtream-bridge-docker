package internal

import (
    "encoding/json"
    "net/http"
    "os"

    "github.com/gin-gonic/gin"
)

var users map[string]string

func loadUsers() {
    data, err := os.ReadFile("users.json")
    if err != nil {
        panic("Missing users.json")
    }

    json.Unmarshal(data, &users)
}

func authenticate(c *gin.Context) bool {
    user := c.Query("username")
    pass := c.Query("password")

    if p, ok := users[user]; ok && p == pass {
        return true
    }
    return false
}

func StartServer() error {
    loadUsers()
    r := gin.Default()

    r.GET("/player_api.php", func(c *gin.Context) {
        if !authenticate(c) {
            c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
            return
        }

        // API skeleton
        data := gin.H{
            "user_info": gin.H{
                "auth":       1,
                "status":     "Active",
                "exp_date":   "0",
                "max_connections": 1,
            },
            "server_info": gin.H{
                "url": "localhost",
            },
            "categories": []any{},
        }

        c.JSON(http.StatusOK, data)
    })

    return r.Run(":10000")
}
