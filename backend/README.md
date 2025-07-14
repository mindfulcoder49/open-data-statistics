Okay, setting up a new server with more RAM is a good move, especially given the Playwright usage. Here's how you can set up the `crontab` to automatically pull your repository and run/update your Docker application:

**1. Prerequisites on the New Server:**

*   **Install Git:**
    ```bash
    sudo apt update
    sudo apt install git -y
    ```
*   **Install Docker:** Follow the official Docker installation guide for Ubuntu: [https://docs.docker.com/engine/install/ubuntu/](https://docs.docker.com/engine/install/ubuntu/)
*   **Install Docker Compose:** This might be installed as part of Docker (as a plugin, `docker compose`) or need separate installation (classic `docker-compose`). Check if `docker compose version` works. If not, install the classic version: [https://docs.docker.com/compose/install/linux/](https://docs.docker.com/compose/install/linux/) (often involves downloading the binary).
    *   Verify installation: `docker compose version` or `docker-compose --version`
*   **Set up SSH Key for GitHub:** Just like you did before (commands 4-6 in your history), create an SSH key on the new server and add the public key (`~/.ssh/id_rsa.pub`) to your GitHub account's deploy keys or your personal SSH keys.
    ```bash
    ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
    cat ~/.ssh/id_rsa.pub
    # Add the output to GitHub
    ssh -T git@github.com # Test connection
    ```

**2. Clone Your Repository:**

*   Navigate to where you want to store the code (e.g., your home directory).
*   Clone the repository using the SSH URL.
    ```bash
    cd ~
    git clone -b origin git@github.com:mindfulcoder49/opportunityHarvester.git #change branch if needed
    cd opportunityHarvester # IMPORTANT: Make sure you are in the repo directory
    ```

**3. DO LetsEncrypt configuration:**

*   Associate Elastic IP with instance
*   Open Security Group to the world
*   sudo certbot certonly --standalone -d myragapp.com -d www.myragapp.com

**4. Determine Full Path for Docker Compose:**

*   Cron jobs run in a minimal environment and often don't have the same `$PATH` as your interactive shell. You need the full path to the `docker-compose` executable (or know if you are using the `docker compose` plugin).
*   Find the path:
    ```bash
    which docker-compose
    ```
    *   This might output `/usr/local/bin/docker-compose`, `/usr/bin/docker-compose`, or something similar. Note this path.
    *   *Alternatively*, if you installed the Docker plugin, you'll use `docker compose` (with a space, no hyphen) and usually need the path to `docker`: `which docker` (likely `/usr/bin/docker`).

**5. Set up the Cron Job:**
*/10 * * * * /home/ubuntu/opportunityHarvester/run_docker_compose.sh

**6. Initial Manual Run:**

*   Before relying on cron, test the commands manually from your repository directory:
    ```bash
    cd /home/ubuntu/opportunityHarvester
    git pull
    # Test EITHER:
    sudo docker-compose up --build -d
    ```
*   Check the status:
    ```bash
    sudo docker ps
    # Check logs if needed
    sudo docker compose logs -f # (Or docker-compose logs -f)
    ```
